# Installation, pas à pas

Tutoriel pour partir de zéro sur **cette machine**, sans rien connaître à Docker ni à Kubernetes.
Chaque étape se termine par une **commande de vérification** et par ce que tu dois voir : si la
sortie ne ressemble pas à ça, l'étape n'est pas franchie, et il ne sert à rien de continuer.

⚠ **Ce qui a été vérifié en écrivant ce document, et ce qui ne l'a pas été.** Les dépôts, les
versions, les URL et le comportement de l'installateur `claude` ont été **mesurés** ici (les
mesures sont dans le texte). En revanche **rien de la partie Docker ni Kubernetes n'a été exécuté** :
ni l'un ni l'autre n'est installé sur cette machine, donc les sections 2 à 5 sont des instructions
fondées sur les sources officielles, pas un compte rendu d'exécution. Les commandes de vérification
sont là précisément pour ça.

## Ce que chaque outil fait ici

| Outil | À quoi il sert dans `forgeron` | Obligatoire ? |
|---|---|---|
| `git` | les worktrees, les branches, les commits | **oui** |
| `python3` | le pilote lui-même (bibliothèque standard uniquement) | **oui** |
| `gh` | issues, pull requests, revues, checks, journaux de CI | **oui** |
| `claude` | l'agent qui code | **oui** |
| `docker` | empaqueter le pilote, et faire tourner un cluster local | non |
| `kubectl` + `k3d` | le cluster local, pour tester le mode « un pod par action » | non |

Les quatre premiers suffisent pour tout faire tourner. Docker et Kubernetes ne débloquent **qu'une**
chose : le parallélisme sur plusieurs machines. Sur celle-ci, `max_concurrent` le fait déjà.

## 0. Ta machine, mesurée

```
Ubuntu 26.04 LTS (resolute) sous WSL2, noyau 6.6.114.1-microsoft-standard-WSL2
systemd : running          <- important, voir 2.1
amd64, 22 coeurs, 39 Gio de RAM, 736 Gio libres
utilisateur dans le groupe sudo
deja installes : git 2.53.0, python 3.14.4, gh 2.46.0, claude 2.1.195
absents : docker, kubectl, k3d, jq
```

Deux conséquences qui décident de tout le reste : **systemd tourne** dans ta distribution WSL2, donc
Docker Engine s'installe nativement et démarre tout seul, sans Docker Desktop ; et tu as 736 Gio et
39 Gio de RAM, donc un cluster local ne te coûtera rien de sensible.

---

## 1. Le socle obligatoire

### 1.1 `git` et `python3` — déjà là

```bash
git --version && python3 --version
```

À voir : `git version 2.53.0` et `Python 3.14.4`. Rien à faire.

### 1.2 `jq` — pas obligatoire, mais confortable

`gh` embarque son propre moteur `jq` (le drapeau `--jq`), donc `forgeron` n'en a **pas** besoin.
C'est utile pour lire des sorties JSON à la main.

```bash
sudo apt-get update && sudo apt-get install -y jq
jq --version
```

### 1.3 `gh` — mettre à jour, et pourquoi ça vaut le coup

Ubuntu 26.04 livre `gh` **2.46.0** ; la version courante est **2.98.0** (mesuré le 2026-08-27). Ce
n'est pas cosmétique : `gh pr checks --json` **n'existe pas** en 2.46, ce qui a obligé `forgeron` à
lire l'agrégat de checks par `gh pr view --json statusCheckRollup`. Ça marche, c'est même plus
robuste — mais autant avoir les deux.

```bash
# 1. la cle du depot officiel GitHub CLI
sudo mkdir -p -m 755 /etc/apt/keyrings
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null
sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg

# 2. le depot (suite "stable", independante de la version d'Ubuntu)
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
  | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null

# 3. installer
sudo apt-get update && sudo apt-get install -y gh
```

**Vérifier :**

```bash
gh --version && gh auth status
```

À voir : `gh version 2.98.x`, puis `Logged in to github.com account MasterLaplace` et
`Token scopes: 'admin:public_key', 'gist', 'read:org', 'repo'`.

Si `gh auth status` dit que tu n'es pas connecté :

```bash
gh auth login --hostname github.com --git-protocol ssh --web
```

⚠ **N'ajoute pas la portée `workflow`.** Son absence est ce qui empêche l'agent de pousser une
modification de `.github/workflows/` : c'est un garde-fou appliqué par le serveur GitHub, pas par un
prompt, et c'est le seul genre qui tienne vraiment.

Une seule portée est à ajouter, et **seulement** si tu veux les webhooks (section « notifier » de
[GITHUB.md](GITHUB.md)) :

```bash
gh auth refresh -s admin:repo_hook
```

### 1.4 `claude` — et **la** question de l'authentification

C'est le point qui t'intéresse : **ne pas payer un supplément d'API alors que tu as déjà un
abonnement.** Il y a trois façons de s'authentifier, et une seule est la bonne pour toi.

| Méthode | Facturé sur | Convient à |
|---|---|---|
| connexion interactive (`claude` puis `/login`) | **ton abonnement** | ton usage quotidien au clavier |
| **`claude setup-token`** → `CLAUDE_CODE_OAUTH_TOKEN` | **ton abonnement** | **l'automatisation, les conteneurs, la CI** |
| `ANTHROPIC_API_KEY` | crédits API, **facturés en plus** | quelqu'un qui n'a pas d'abonnement |

**Donc : `claude setup-token`.** C'est exactement le mécanisme fait pour ça — la commande le dit
elle-même : *« Set up a long-lived authentication token (requires Claude subscription) »*. Il n'y a
aucune raison de toucher à `ANTHROPIC_API_KEY`.

#### Installer

Déjà fait sur cette machine (`~/.local/bin/claude` → version 2.1.195). Pour une machine neuve ou un
conteneur :

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

⚠ **Sans `sudo`.** L'installateur refuse explicitement d'être lancé sous `sudo` depuis le shell d'un
utilisateur, et la raison est écrite dans son propre code : sous `sudo`, `$HOME` devient
`/root`, le binaire atterrit dans `/root/.local/bin`, et la commande `claude` reste introuvable dans
ton shell. (Vérifié dans le script : la garde ne se déclenche que si `id -u` vaut 0 **et** que
`SUDO_USER` est renseigné. **Un root simple, dans un conteneur, passe** — c'est ce qui rend le
Dockerfile de la section 4 possible.)

**Vérifier :**

```bash
claude --version && echo 'echo ok' | claude -p --tools "" --model sonnet
```

À voir : `2.1.x (Claude Code)` puis une réponse du modèle. ⚠ Le prompt part sur **stdin** :
`--tools` est un drapeau *variadique*, donc un prompt placé après lui serait avalé comme une valeur
de plus, et `claude` répondrait « Input must be provided ». C'est mesuré, et c'est pour ça que
`forgeron` passe toujours par stdin.

#### Le token longue durée, en pratique

```bash
claude setup-token
```

Ça ouvre une page de connexion à **ton compte** et rend un token. Range-le tout de suite dans un
fichier à toi seul, jamais dans une variable d'environnement tapée à la main (elle finirait dans
l'historique de ton shell) :

```bash
mkdir -p ~/.forgeron && touch ~/.forgeron/secrets.env && chmod 600 ~/.forgeron/secrets.env
# puis, dans un editeur :
#   CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat...
```

**Vérifier** que le token suffit, **sans** ta session interactive — c'est tout l'intérêt :

```bash
env -i PATH="$PATH" HOME="$HOME" \
  CLAUDE_CODE_OAUTH_TOKEN="$(grep -oP '(?<=^CLAUDE_CODE_OAUTH_TOKEN=).*' ~/.forgeron/secrets.env)" \
  bash -c 'echo "dis juste: ok" | claude -p --tools "" --model sonnet'
```

À voir : une réponse du modèle. `env -i` vide l'environnement, donc si ça répond, c'est bien le
token qui a servi.

#### ⚠ Ce que ce token est, et les trois pièges

1. **C'est une clé de ton abonnement**, pas une clé d'API jetable. Traite-la comme un mot de passe :
   jamais dans un `Dockerfile`, jamais dans une image, jamais dans git, jamais en argument
   `-e TOKEN=...` sur une ligne de commande (l'historique du shell la garde). Toujours un fichier en
   `600`, ou un `Secret` Kubernetes.
2. **Ton abonnement est un plan `team`** (lu dans `~/.claude/.credentials.json`). Un agent qui tourne
   sans surveillance consomme donc **les mêmes limites de débit que toi au clavier**. Une boucle
   emballée ne te coûtera pas d'argent — elle peut te bloquer *toi* pendant un moment. C'est le vrai
   coût, et c'est ce que bornent `max_rounds`, `max_check_fixes` et `max_spend_usd`.
3. **`max_spend_usd` n'est pas une facture** sur abonnement : c'est un *indicateur d'usage* calculé
   à partir des jetons (mesuré : un run trivial rapporte `total_cost_usd = 0.044`, dont l'essentiel
   est la mise en cache du prompt système). Le plafond arrête quand même une boucle emballée, ce qui
   est sa seule raison d'être.

⚠ Et un piège de conception à connaître : le drapeau **`--bare` est inutilisable** avec un
abonnement. Son aide le dit : *« Anthropic auth is strictly ANTHROPIC_API_KEY or apiKeyHelper (OAuth
and keychain are never read) »*. Il faudrait donc payer l'API pour l'utiliser. `forgeron` ne s'en
sert pas.

### 1.5 Vérifier le socle d'un coup

```bash
cd ~/LplCraftSkills/forgeron && ./tests/run.sh && python3 -m forgeron doctor
```

À voir : `Ran 47 tests ... OK`, `9/9 mutations detectees`, puis `doctor` avec les vérifications
requises passées. Les deux lignes `note` (portées `admin:repo_hook` et `workflow`) sont normales :
ce sont des absences voulues.

**À ce stade tout `forgeron` fonctionne.** Les sections suivantes sont pour apprendre Docker et
Kubernetes, et pour préparer le mode multi-machines. Tu peux t'arrêter ici sans rien perdre.

---

## 2. Docker

### 2.1 Docker Desktop ou Docker Engine ? — prends Engine

Deux routes existent sous WSL2, et **une seule est simple sur ta machine** :

| | Docker Desktop (côté Windows) | **Docker Engine (dans WSL2)** |
|---|---|---|
| ce que tu installes | une application Windows + intégration WSL | des paquets `apt`, comme n'importe quel Linux |
| démarrage | il faut lancer Docker Desktop | `systemd` le démarre au boot de la distro |
| exige | rien de spécial | **que `systemd` tourne** — c'est ton cas |
| interface graphique | oui | non (`docker` en ligne de commande) |
| licence | payante pour les grandes entreprises | Apache 2.0, sans condition |

`systemd` tourne dans ta distribution, donc **Docker Engine natif** : une couche en moins, aucune
dépendance à une application Windows, aucune question de licence. C'est cette route qui suit.

*(Si tu préfères Docker Desktop : installe-le sous Windows, active « WSL integration » pour
`Ubuntu-26.04` dans ses réglages, et saute directement en 2.4. Les deux ne peuvent pas cohabiter
proprement — choisis-en une.)*

### 2.2 Installer Docker Engine

Le dépôt officiel Docker **a bien une suite `resolute`** pour Ubuntu 26.04 (vérifié : HTTP 200 sur
`download.docker.com/linux/ubuntu/dists/resolute/Release`). Pas besoin de bricoler un nom de code
plus ancien.

```bash
# 1. de quoi parler a un depot en HTTPS
sudo apt-get update
sudo apt-get install -y ca-certificates curl

# 2. la cle de signature de Docker
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# 3. le depot, pour TA version d'Ubuntu
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 4. le moteur, le client, et les deux greffons utiles
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

# 5. demarrer maintenant, et a chaque demarrage de la distro
sudo systemctl enable --now docker
```

**Vérifier :**

```bash
sudo systemctl is-active docker && sudo docker run --rm hello-world
```

À voir : `active`, puis un paragraphe qui commence par
`Hello from Docker! This message shows that your installation appears to be working correctly.`

### 2.3 Se passer de `sudo` — et le piège qui suit

Parler à Docker sans `sudo` veut dire appartenir au groupe `docker` :

```bash
sudo usermod -aG docker "$USER"
```

⚠ **Cette ligne ne prend pas effet dans le shell où tu la tapes.** Un groupe est lu à l'ouverture de
la session, donc `docker ps` continuera de répondre `permission denied` et tu croiras que la
commande a échoué. Trois façons d'en sortir, de la plus locale à la plus propre :

```bash
newgrp docker        # seulement dans CE shell
# ou : fermer et rouvrir le terminal
# ou, le plus sur sous WSL, depuis PowerShell cote Windows :
#   wsl --terminate Ubuntu-26.04
```

**Vérifier :**

```bash
docker ps && id -nG | tr ' ' '\n' | grep -x docker
```

À voir : un tableau vide avec ses en-têtes (`CONTAINER ID  IMAGE  ...`), **sans `sudo`**, puis
`docker`.

⚠ Appartenir au groupe `docker` équivaut à être root sur la machine : le démon tourne en root et
peut monter n'importe quel répertoire de l'hôte. Ce n'est pas grave sur ta machine de développement,
mais ce n'est pas « un groupe de plus ».

### 2.4 Les six mots de Docker, et rien d'autre

Il n'y a que six choses à comprendre pour tout ce qui suit.

| Mot | Ce que c'est | L'analogie qui marche |
|---|---|---|
| **image** | un système de fichiers figé, en lecture seule, avec une commande par défaut | un exécutable |
| **conteneur** | une image en cours d'exécution, avec sa propre vue du système | un processus |
| **`Dockerfile`** | la recette qui construit une image, une instruction par couche | un `Makefile` |
| **volume** / *bind mount* | un répertoire de l'hôte visible dans le conteneur | un dossier partagé |
| **registre** | là où les images vivent (Docker Hub, ghcr.io) | un dépôt de paquets |
| **compose** | un fichier qui décrit un ou plusieurs conteneurs et leurs réglages | un script de lancement versionné |

Deux règles qui évitent 90 % des ennuis de débutant :

- **un conteneur qui s'arrête perd tout ce qui n'est pas dans un volume.** C'est voulu : c'est ce qui
  rend une image reproductible. Ce que tu veux garder se monte ;
- **une couche d'image est publique une fois l'image poussée.** Un secret écrit dans un `Dockerfile`
  y reste **même si une instruction suivante le supprime** — les couches sont empilées, pas
  réécrites. D'où la section 4.2.

### 2.5 Si ça ne marche pas

| Symptôme | Cause probable | Remède |
|---|---|---|
| `Cannot connect to the Docker daemon` | le démon ne tourne pas | `sudo systemctl status docker`, puis `sudo systemctl start docker` |
| `permission denied ... docker.sock` | groupe pas encore actif | 2.3, le piège du `newgrp` |
| `failed to resolve ... no such host` pendant un build | DNS de WSL2 cassé | `cat /etc/resolv.conf` ; en dernier recours mettre `nameserver 1.1.1.1` et `[network] generateResolvConf = false` dans `/etc/wsl.conf` |
| `iptables` / erreurs réseau au démarrage du démon | conflit `nftables` / `iptables-legacy` | `sudo update-alternatives --config iptables`, choisir `iptables-nft`, puis redémarrer le démon |
| tout marchait, puis plus rien après un redémarrage Windows | la distro a redémarré sans le démon | `sudo systemctl enable docker` (le `enable` de l'étape 5) |

---

## 3. Kubernetes en local

### 3.1 Pourquoi `k3d`, et pas les autres

Un « cluster local » veut dire faire tourner le plan de contrôle de Kubernetes sur ta machine. Trois
façons, et la différence est concrète :

| | poids | démarrage | remarque |
|---|---|---|---|
| Kubernetes de Docker Desktop | lourd | lent | lié à Docker Desktop, une seule version |
| `minikube` | moyen | ~1 min | crée une VM ou un conteneur, beaucoup d'options |
| **`k3d`** | **léger** | **~30 s** | lance **k3s** (un Kubernetes complet, allégé) **dans des conteneurs Docker** |

`k3d` gagne pour apprendre : un cluster se crée et se détruit en une commande, plusieurs peuvent
cohabiter, et comme ce sont des conteneurs Docker tu peux **voir** de quoi un cluster est fait avec
un `docker ps`. C'est pédagogiquement précieux : Kubernetes cesse d'être une boîte noire.

Version courante mesurée le 2026-08-27 : **k3d v5.9.0** (l'alternative `kind` est en v0.33.0 et
ferait tout aussi bien l'affaire).

### 3.2 `kubectl`

`kubectl` est le client : il parle à l'API d'un cluster. Il s'installe séparément du cluster, et il
n'a **pas besoin** de Docker.

```bash
# depot officiel Kubernetes, independant de la version d'Ubuntu
sudo mkdir -p -m 755 /etc/apt/keyrings
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.37/deb/Release.key \
  | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
sudo chmod 644 /etc/apt/keyrings/kubernetes-apt-keyring.gpg

echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.37/deb/ /' \
  | sudo tee /etc/apt/sources.list.d/kubernetes.list > /dev/null
sudo chmod 644 /etc/apt/sources.list.d/kubernetes.list

sudo apt-get update && sudo apt-get install -y kubectl
```

⚠ Le numéro `v1.37` est **dans l'URL du dépôt**, pas résolu automatiquement : c'est voulu par le
projet Kubernetes, pour qu'une mise à jour de version mineure soit un acte volontaire. Pour changer
de version plus tard, tu édites cette ligne. (Vérifié : `v1.34` à `v1.37` répondent tous ;
`dl.k8s.io/release/stable.txt` annonce `v1.37.0`.)

**Vérifier :**

```bash
kubectl version --client
```

À voir : `Client Version: v1.37.x`. Il dira aussi qu'il ne joint aucun serveur — normal, il n'y a
pas encore de cluster.

### 3.3 `k3d`, et ton premier cluster

```bash
curl -sS https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash
```

⚠ Ce script écrit dans `/usr/local/bin`, donc il demandera `sudo` tout seul. Si tu préfères le lire
avant de l'exécuter — bonne habitude pour tout `curl | bash` :

```bash
curl -sS https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh -o /tmp/k3d-install.sh
less /tmp/k3d-install.sh && bash /tmp/k3d-install.sh
```

Puis le cluster :

```bash
k3d cluster create forgeron --agents 2
```

Trois choses se passent, et tu peux les voir : `--agents 2` crée **deux nœuds de travail** en plus
du serveur, k3d écrit la configuration de connexion dans `~/.kube/config`, et `kubectl` s'en sert
tout seul.

**Vérifier :**

```bash
kubectl get nodes
docker ps --format '{{.Names}}\t{{.Image}}'
```

À voir : trois nœuds `Ready` (`k3d-forgeron-server-0`, `k3d-forgeron-agent-0`, `-agent-1`), et le
`docker ps` qui montre **les mêmes noms** — la preuve directe qu'un « nœud » Kubernetes est ici un
simple conteneur.

### 3.4 Les six objets à comprendre, et rien de plus

Kubernetes en a des dizaines. Six suffisent pour tout ce dont on parle ici.

| Objet | Ce que c'est | Quand tu en veux un |
|---|---|---|
| **Pod** | un ou plusieurs conteneurs qui partagent une adresse réseau | jamais directement : on les crée par un objet au-dessus |
| **Deployment** | « garde N pods de ce type vivants en permanence » | un service qui doit tourner tout le temps — le réconciliateur |
| **Job** | « exécute ce pod **jusqu'à ce qu'il réussisse**, puis arrête » | une tâche bornée — **une action de `forgeron`** |
| **Secret** | des données sensibles, montées en fichier ou en variable | le `CLAUDE_CODE_OAUTH_TOKEN`, le token GitHub |
| **ConfigMap** | la même chose, pour ce qui n'est pas sensible | `config.json` de `forgeron` |
| **Namespace** | une cloison entre groupes d'objets | isoler ces essais du reste |

L'idée qui les relie, et c'est **la même** que celle de `forgeron` : tu déclares l'état voulu, et une
boucle de réconciliation s'arrange pour que le réel y ressemble. Tu ne dis jamais « lance ce
conteneur » ; tu dis « il doit y en avoir trois », et si l'un meurt, quelque chose le remplace.

C'est aussi ce qui explique le découpage de [CLUSTER.md](CLUSTER.md) : **un `Deployment` décide, un
`Job` exécute une action.** Un Job par action et non par issue, parce qu'une action est bornée (un
run d'agent) alors qu'une issue vit des jours.

### 3.5 Ton premier Job, en vrai

Rien à voir avec `forgeron` : le but est de voir le cycle complet une fois.

```bash
kubectl create namespace bac-a-sable

cat <<'YML' | kubectl apply -n bac-a-sable -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: bonjour
spec:
  backoffLimit: 2            # nombre de reprises avant d'abandonner
  template:
    spec:
      restartPolicy: Never   # obligatoire pour un Job : il finit, il ne redemarre pas
      containers:
        - name: bonjour
          image: busybox:1.37
          command: ["sh", "-c", "echo 'depuis un pod'; sleep 3; echo termine"]
YML

kubectl get jobs -n bac-a-sable -w      # Ctrl-C pour arreter de regarder
kubectl logs -n bac-a-sable job/bonjour
```

À voir : le Job passe à `COMPLETIONS 1/1`, et les logs affichent `depuis un pod` puis `termine`.

Puis regarde ce qui se passe quand **ça échoue** — c'est ce que tu rencontreras en vrai :

```bash
cat <<'YML' | kubectl apply -n bac-a-sable -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: casse
spec:
  backoffLimit: 2
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: casse
          image: busybox:1.37
          command: ["sh", "-c", "echo 'je vais echouer'; exit 1"]
YML

kubectl get pods -n bac-a-sable
kubectl describe job/casse -n bac-a-sable | tail -20
```

À voir : trois pods en `Error` (l'essai plus deux reprises), et à la fin du `describe` la raison
`BackoffLimitExceeded`. **C'est le réflexe de diagnostic à retenir** : `kubectl get pods` dit *quoi*,
`kubectl describe` dit *pourquoi*, `kubectl logs` dit *ce que le programme a écrit*. Les trois, dans
cet ordre.

Nettoyer :

```bash
kubectl delete namespace bac-a-sable
```

⚠ Supprimer un namespace supprime **tout** ce qu'il contient. C'est la façon la plus sûre de nettoyer
des essais, et la plus dangereuse de nettoyer autre chose.

---

## 4. Faire tourner `forgeron` en conteneur

⚠ **Deux préalables**. Cette section suppose qu'ils sont
faits, ce qu'elle ne disait pas, et le symptôme est trompeur : `docker compose` **crée
silencieusement** le répertoire hôte d'un montage absent, donc `~/forgeron-sandbox` apparaît vide
et `git` échouera bien plus tard, loin de la cause.

1. **le dépôt bac à sable existe et est cloné.** Le bloc complet est en fin de
   [GITHUB.md](GITHUB.md), et il commence par `gh repo create forgeron-sandbox --private --clone` ;
2. **`~/.forgeron/config.json` existe**, ce qui est l'objet du 4.3 ci-dessous.

Vérifier les deux avant d'aller plus loin, sinon le conteneur démarre et s'arrête sur un message
qui ne nomme que le second :

```bash
git -C ~/forgeron-sandbox log --oneline -1   # doit rendre un commit, pas « not a git repository »
test -f ~/.forgeron/config.json && echo ok
```

⚠ **Rien de cette section n'a été exécuté.** L'image n'a pas été construite, le Job n'a pas été
appliqué. Ce qui **a** été vérifié, c'est que les fichiers sont cohérents avec le code : 11 tests de
[`tests/test_deployment_files.py`](../tests/test_deployment_files.py) relisent le `ConfigMap` avec le
**vrai** chargeur de configuration, vérifient que les chemins montés sont ceux que la configuration
nomme, que les trois fichiers s'accordent sur l'étiquette d'image, qu'aucun secret n'est cuit dans le
`Dockerfile`, et que l'entrypoint refuse de démarrer sans authentification.

### 4.1 Construire l'image

```bash
cd ~/LplCraftSkills/forgeron
docker build -f docker/Dockerfile -t forgeron:0.1.0 .
```

⚠ **Le `.` final est le contexte, et il doit être la racine de `forgeron/`**, pas `docker/` — le
`Dockerfile` copie `forgeron/` et `docker/entrypoint.sh`, qui sont tous deux relatifs à cette racine.

**Vérifier :**

```bash
docker run --rm forgeron:0.1.0 --version
docker run --rm --entrypoint python3 forgeron:0.1.0 -m forgeron --help | head -3
```

À voir : le premier échoue avec `ERREUR : aucune authentification claude` **et c'est le résultat
attendu** — l'entrypoint vérifie avant d'agir. Le second contourne l'entrypoint et doit afficher
l'aide.

### 4.2 L'authentification dans un conteneur : deux options

**Option A — le token d'abonnement. C'est celle à prendre.**

```bash
# le fichier de la section 1.4, en 600, hors de tout depot
cat ~/.forgeron/secrets.env
#   CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat...
#   GH_TOKEN=...                     <- `gh auth token` le donne

docker run --rm --env-file ~/.forgeron/secrets.env forgeron:0.1.0 --version
```

À voir : `[entrypoint] claude : token d'abonnement (CLAUDE_CODE_OAUTH_TOKEN)` puis `forgeron 0.1.0`.

⚠ `--env-file` et **jamais** `-e CLAUDE_CODE_OAUTH_TOKEN=sk-...` : la seconde forme met le token dans
l'historique de ton shell et dans la table des processus, où n'importe quel programme de la machine
peut le lire pendant la durée du run.

**Option B — monter tes credentials. Local seulement, et voici le prix exact.**

```bash
docker run --rm \
  -e CLAUDE_CONFIG_DIR=/claude \
  -v ~/.claude:/claude \
  forgeron:0.1.0 --version
```

Ça marche parce que `claude` lit `CLAUDE_CONFIG_DIR` (vérifié dans le binaire). Trois raisons de ne
pas en faire l'option par défaut :

1. le montage doit être **en lecture-écriture**, parce que le token d'accès expire et que `claude` le
   rafraîchit sur place. Un montage `:ro` marche… jusqu'à l'expiration, puis échoue au milieu d'un
   run ;
2. le conteneur voit donc ton `refreshToken`, c'est-à-dire de quoi rester connecté à ton compte. Un
   token de `setup-token` est révocable seul ; ton refresh token, non ;
3. deux processus qui rafraîchissent le même fichier peuvent se marcher dessus — ta session
   interactive et le conteneur.

En cluster, l'option B est de toute façon exclue : il n'y a pas de `~/.claude` à monter.

### 4.3 La configuration, puis la boucle

[`docker/compose.yaml`](../docker/compose.yaml) monte deux choses et rien d'autre : `~/.forgeron`
(l'état, la seule chose qui doit survivre au conteneur) et le clone dont les worktrees sont tirés.

Le pilote ne démarre pas sans configuration, et il n'en invente pas :

```bash
mkdir -p ~/.forgeron
cat > ~/.forgeron/config.json <<'JSON'
{
  "repos": [
    {
      "slug": "TON_LOGIN/forgeron-sandbox",
      "path": "/repos/forgeron-sandbox",
      "base": "main",
      "labels": ["claude"],
      "hold_label": "claude:hold",
      "reviewers": ["TON_LOGIN"]
    }
  ],
  "limits": { "max_rounds": 6, "max_spend_usd": 12.0, "auto_merge": false },
  "max_concurrent": 1,
  "poll_seconds": 60,
  "model": "sonnet",
  "budget_per_run_usd": 3.0,
  "continuity": "resume"
}
JSON
```

Deux choses à comprendre dans ce fichier, et elles se contredisent d'apparence.

⚠ **`path` est le chemin vu du CONTENEUR** (`/repos/forgeron-sandbox`), jamais celui de ton `$HOME`.
C'est la première chose qui casse quand on recopie une configuration locale, et le symptôme (`gh`
répond bien, `git` échoue) n'a rien qui désigne la cause. Conséquence directe : **ce fichier ne sert
pas aux deux côtés**. Une passe lancée depuis l'hôte veut son propre fichier, et `--config` est là
pour ça.

À l'inverse, **`home` est délibérément absent** : il se dérive de `$HOME` à l'exécution, donc le même
fichier tombe sur `/home/forgeron/.forgeron` dans le conteneur et sur le tien à l'extérieur. Un
chemin écrit en dur y casserait exactement ce que son absence fait marcher.

*(`forgeron config --init` écrit un squelette équivalent, mais avec des chemins d'hôte : il sert
pour une utilisation locale, pas pour celle-ci.)*

Puis la boucle :

```bash
# une passe, sans ecrire : le meilleur premier essai
docker compose -f docker/compose.yaml run --rm forgeron \
  --config /home/forgeron/.forgeron/config.json once

# la boucle, en fond
docker compose -f docker/compose.yaml up -d
docker compose -f docker/compose.yaml logs -f
```

⚠ Le clone est monté **en lecture-écriture**, et ce n'est pas une négligence : `git worktree add`
écrit dans le `.git` du clone. Un montage `:ro` échouerait dès la première passe.

### 4.4 Dans le cluster `k3d`

```bash
cd ~/LplCraftSkills/forgeron

# 1. rendre l'image visible au cluster. SANS CETTE ETAPE le pod reste en
#    ErrImagePull : les noeuds k3d sont des conteneurs avec leur propre stockage
#    d'images, donc une image construite sur l'hote leur est invisible.
k3d image import forgeron:0.1.0 -c forgeron

# 2. la cloison et la configuration
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/20-configmap.yaml

# 3. le secret, sans qu'il touche git : depuis TON fichier en 600
kubectl create secret generic forgeron -n forgeron \
  --from-env-file="$HOME/.forgeron/secrets.env"

# 4. une passe
kubectl apply -f k8s/30-job.yaml
kubectl get pods -n forgeron -w        # Ctrl-C pour arreter de regarder
kubectl logs -n forgeron job/forgeron-une-passe
```

**Vérifier :** le pod passe par `ContainerCreating` puis `Running` puis `Completed`, et les logs
commencent par la ligne d'entrypoint qui nomme le mode d'authentification.

Le réflexe de diagnostic, dans cet ordre, comme en 3.5 :

```bash
kubectl get pods -n forgeron                  # QUOI
kubectl describe pod -n forgeron -l job-name=forgeron-une-passe | tail -25   # POURQUOI
kubectl logs -n forgeron job/forgeron-une-passe                              # CE QU'IL A DIT
```

⚠ **Trois limites connues de ce Job, écrites plutôt que découvertes :**

1. le volume `state` est un `emptyDir`, donc **l'état meurt avec le pod**. Suffisant pour un `once`,
   pas pour la boucle : chaque passe redécouvrirait les issues depuis zéro et replanifierait tout.
   Il faut un `PersistentVolumeClaim` ;
2. le volume `repos` est vide, donc **il n'y a aucun clone**. Le Job échouera à la préparation du
   worktree. C'est le point 3 de [CLUSTER.md](CLUSTER.md) : en pod il faut un `git clone
   --filter=blob:none` au démarrage, ou un PVC de cache. C'est le seul endroit où le code suppose une
   machine de développement ;
3. le `ConfigMap` met `continuity: "rebuild"`, **et ce n'est pas un réglage de confort** : une session
   `claude` est rangée sous un slug de son répertoire de travail, donc un pod ne peut pas reprendre
   une conversation créée ailleurs. `"resume"` ici ne planterait pas — il repartirait d'une
   conversation vide en prétendant continuer, ce qui est pire.

Autrement dit : **le mode cluster n'est pas terminé**, et ce sont ces trois points qui restent. Le
mode local, lui, l'est.

---

## 5. Tout vérifier d'un coup

À coller tel quel : chaque ligne dit `ok` ou nomme ce qui manque.

```bash
for outil in git python3 gh claude jq docker kubectl k3d; do
  if command -v "$outil" > /dev/null; then
    printf 'ok      %-10s %s\n' "$outil" "$(command -v "$outil")"
  else
    printf 'ABSENT  %-10s\n' "$outil"
  fi
done

echo
gh auth status 2>&1 | grep -E 'Logged in|Token scopes' || echo 'ABSENT  session gh'
systemctl is-active docker 2>/dev/null | sed 's/^/docker daemon : /'
kubectl get nodes --no-headers 2>/dev/null | wc -l | sed 's/^/noeuds kube  : /'
echo
cd ~/LplCraftSkills/forgeron && ./tests/run.sh 2>&1 | grep -E 'Ran |^OK|mutations detectees'
python3 -m forgeron doctor
```

## 6. Tout désinstaller

Dans cet ordre — le cluster avant Docker, puisqu'il tourne dedans.

```bash
# le cluster local
k3d cluster delete forgeron
sudo rm -f /usr/local/bin/k3d

# kubectl
sudo apt-get remove -y kubectl
sudo rm -f /etc/apt/sources.list.d/kubernetes.list /etc/apt/keyrings/kubernetes-apt-keyring.gpg

# docker : la premiere commande garde tes volumes, la seconde les detruit
sudo apt-get remove -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
# sudo rm -rf /var/lib/docker /var/lib/containerd     <- IRREVERSIBLE
sudo rm -f /etc/apt/sources.list.d/docker.list /etc/apt/keyrings/docker.asc
sudo gpasswd -d "$USER" docker

# claude (l'installateur met tout sous $HOME, rien n'est a supprimer en root)
rm -rf ~/.local/share/claude ~/.local/bin/claude
# ~/.claude contient tes credentials ET l'historique de tes sessions : a supprimer
# volontairement, jamais par reflexe de nettoyage.

# forgeron : l'etat, les worktrees et le journal
rm -rf ~/.forgeron
```

⚠ `rm -rf ~/.forgeron` supprime les worktrees en cours. **Les branches, elles, sont sur GitHub** —
c'est tout l'intérêt : la branche est le seul instantané qui survit à la machine. Rien de ce qui a
été poussé n'est perdu.

---

## 7. Spécificités WSL2

Tout ce qui précède est écrit pour **ta** configuration : Ubuntu 26.04 LTS sous WSL2, `systemd`
actif. Ces cinq points sont propres à WSL2 et n'apparaissent dans aucune documentation Docker ou
Kubernetes, parce qu'ils ne concernent qu'ici.

### 7.1 `systemd` — déjà bon, mais vérifie si tu changes de distro

```bash
cat /proc/1/comm        # doit dire : systemd
```

Si un jour ça dit `init` ou `sh`, `systemctl enable --now docker` ne marchera pas. Le remède est côté
distro, dans `/etc/wsl.conf` :

```ini
[boot]
systemd=true
```

puis, **depuis PowerShell côté Windows** : `wsl --shutdown`. Un `wsl --terminate` ne suffit pas
toujours pour un changement de `wsl.conf`.

### 7.2 ⚠ L'horloge dérive après une mise en veille de Windows

C'est **le** piège WSL2 qui fait perdre une soirée, parce que le symptôme ne désigne jamais la
cause : au réveil du PC, l'horloge de la VM WSL peut être décalée de plusieurs minutes ou heures.
Conséquences observables : `gh` répond `certificate is not yet valid` ou `401`, `claude` refuse le
token comme expiré, `docker pull` échoue sur une signature. Tout a l'air d'un problème
d'authentification, et c'est un problème d'heure.

```bash
date                              # comparer avec l'heure de Windows
sudo hwclock --hctosys            # resynchroniser depuis l'horloge materielle
```

Si ça arrive souvent, `sudo apt-get install -y systemd-timesyncd` et
`sudo systemctl enable --now systemd-timesyncd`.

### 7.3 La mémoire et le disque sont partagés par toute la VM

Docker, `k3d` et tes builds vivent **dans la même VM WSL** : les 39 Gio de RAM et les 736 Gio que tu
as vus en section 0 sont un budget commun, pas un par outil. Par défaut WSL prend jusqu'à la moitié
de la RAM de Windows. Pour le borner, un fichier **côté Windows**, dans
`C:\Users\<toi>\.wslconfig` :

```ini
[wsl2]
memory=24GB
processors=16
```

puis `wsl --shutdown` depuis PowerShell.

⚠ **Le disque de WSL grossit et ne rétrécit jamais tout seul.** Les images Docker s'accumulent dans
le VHDX, et supprimer les images libère l'espace *dans* WSL sans rendre un octet à Windows :

```bash
docker system df                  # ce que Docker occupe reellement
docker system prune -a --volumes  # ATTENTION : supprime aussi les volumes non utilises
```

Pour vraiment récupérer la place côté Windows, il faut compacter le VHDX (`wsl --shutdown` puis
`Optimize-VHD` ou `diskpart compact vdisk`) — hors sujet ici, mais bon à savoir avant de s'étonner.

### 7.4 `localhost` traverse, dans un sens seulement

Un port ouvert dans WSL2 est joignable depuis Windows sur `localhost` — donc le tableau de bord d'un
service dans `k3d`, ou le port `8787` de `gh webhook forward`, s'ouvre dans ton navigateur Windows
sans rien configurer.

⚠ L'inverse n'est pas vrai : depuis WSL, `localhost` désigne **WSL**, pas Windows. Pour joindre un
service qui tourne côté Windows, il faut l'IP de l'hôte :

```bash
ip route show default | awk '{print $3}'      # l'adresse de Windows vue de WSL
```

### 7.5 Docker Desktop et Docker Engine ne cohabitent pas

Si tu installes Docker Desktop plus tard, il crée sa propre `/var/run/docker.sock` dans les distros
où l'intégration est activée, et les deux se disputeront la socket. Choisis-en un. Pour vérifier
lequel te répond :

```bash
docker context ls        # celui marque d'une * est actif
docker info --format '{{.OperatingSystem}} / {{.ServerVersion}}'
```

À voir avec Docker Engine natif : un système d'exploitation Debian/Ubuntu. Avec Docker Desktop : une
mention `Docker Desktop`.
