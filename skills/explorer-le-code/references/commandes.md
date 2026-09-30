# Les commandes de l'exploration, et ce que chacune répond

Ce fichier ne se lit pas d'affilée : on y vient quand `SKILL.md` y renvoie, avec une question. Chaque
commande est rangée sous la question à laquelle elle répond.

> Les commentaires des blocs de code restent sans accents : ils sont destinés à être copiés dans un
> terminal. Toutes les commandes se lancent **depuis la racine du dépôt exploré**, sauf mention
> contraire.

## La première heure

### Qu'est-ce qu'il y a dans ce dépôt, et où est la masse ?

```bash
git ls-files | head -50                        # ce qui est versionne (ignore le genere non suivi)
git ls-files | sed 's|/[^/]*$||' | sort | uniq -c | sort -rn | head -20   # dossiers les plus peuples
scc .            # ou tokei, ou cloc : lignes par langage, en separant code, commentaires et vide
```

Un dossier énorme dans une langue inattendue est souvent du généré ou du vendu : le vérifier avant de
le lire.

### Comment on construit et on teste, vraiment ?

```bash
ls .github/workflows/ 2>/dev/null; ls azure-pipelines*.yml Jenkinsfile .gitlab-ci.yml 2>/dev/null
cat package.json | jq .scripts                 # Node : les scripts declares
grep -rn "dotnet test\|npm test\|pytest\|cargo test\|ctest" .github/ 2>/dev/null   # la commande de CI
```

| Écosystème | Construire | Tester | Lancer UN test |
|---|---|---|---|
| Node / TS | `npm ci && npm run build` | `npm test` | `npx vitest run -t "<nom>"` ou `npx jest -t "<nom>"` |
| .NET | `dotnet build` | `dotnet test` | `dotnet test --filter "FullyQualifiedName~<Nom>"` |
| Python | `pip install -e .` ou `uv sync` | `pytest` | `pytest -k "<nom>"` |
| Rust | `cargo build` | `cargo test` | `cargo test <nom>` |
| C / C++ (CMake) | `cmake -B build && cmake --build build` | `ctest --test-dir build` | `ctest --test-dir build -R <nom>` |

La commande de la CI prime sur ce tableau : elle porte les options que le projet exige vraiment.

**Construire exécute du code du dépôt** : scripts d'installation des paquets, tâches de build, hooks.
Pour un dépôt dont on ne connaît pas la provenance, le faire dans un conteneur ou un environnement
isolé (un `venv` en Python plutôt que l'installation globale), et pour seulement lire les dépendances
sans rien exécuter : `npm ci --ignore-scripts`.

### Qui travaille ici, et sur quoi ?

```bash
git log --oneline -30                          # ce qui bouge en ce moment
git shortlog -sn --since="12 months ago" HEAD  # qui contribue, par nombre de commits
git shortlog -sn HEAD -- <chemin>              # qui connait CE dossier : a qui demander
```

Le `HEAD` n'est pas décoratif : sans révision, `git shortlog` lancé dans un script ou un pipe lit
l'entrée standard au lieu de l'historique, et rend un résultat vide.

## Trouver le code derrière un comportement

```bash
rg -n "Texte exact affiche a l'ecran"          # la chaine litterale, d'abord
rg -n "cle.de.traduction" --glob '*.json'      # si l'interface passe par une cle de traduction
rg -n "'/api/orders'" -g '!*.test.*'           # une route, hors tests
rg -n --type cs "class \w+Handler\b"           # une convention de nommage, pas un nom
rg -uuu -n "Texte exact"                       # SANS respecter .gitignore : genere, cache, binaire
```

Un zéro n'est pas une absence : chaîne construite par concaténation, traduite, venue du serveur,
simplement mal recopiée, ou dans un fichier que `rg` saute par défaut (ignoré, caché, binaire).
Chercher un morceau plus court, ou lire la chaîne dans le source avant de la chercher.

Pour les **appelants** d'un symbole, préférer l'éditeur (« trouver toutes les références »,
« hiérarchie d'appels ») à `rg` dès que le nom est commun : l'éditeur résout les surcharges, les
homonymes et les imports, `rg` non.

## Remonter l'histoire

### Qui a écrit cette ligne, et dans quel commit ?

```bash
git blame -w -C -C -C -- <fichier>             # -w ignore les espaces ; -C x3 suit les deplacements et copies
git blame -L 120,140 -- <fichier>              # seulement ces lignes
git blame --ignore-revs-file .git-blame-ignore-revs -- <fichier>   # saute les commits de reformatage
git config blame.ignoreRevsFile .git-blame-ignore-revs   # ECRIT la config locale ; seulement si le fichier existe
git show <sha>                                 # le commit entier : ce qui a change EN MEME TEMPS
```

Un `blame` qui tombe sur un commit de reformatage massif ne dit rien : `.git-blame-ignore-revs` existe
précisément pour le sauter.

### Depuis quand ça existe, et quand ça a disparu ?

```bash
git log -S'plan.first.json' --oneline          # commits ou le NOMBRE d'occurrences de la chaine change
git log -G'retry\([[:space:]]*[0-9]+' --oneline   # commits dont le diff ajoute ou retire une ligne qui correspond
git log -L :compute_total:billing/invoice.py   # l'histoire d'UNE fonction, commit par commit
git log -L 40,60:billing/invoice.py            # l'histoire d'un intervalle de lignes
git log --follow --oneline -- <fichier>        # a travers les renommages
git log --diff-filter=D --name-only --oneline -- <chemin>   # les fichiers SUPPRIMES sous ce chemin
git show <sha>^:<chemin/du/fichier>            # le contenu d'un fichier supprime, juste avant sa suppression
```

`-S` répond à « quand cette chaîne est-elle apparue ou partie ? » ; `-G` répond à « quand une ligne de
cette forme a-t-elle été touchée ? », y compris quand elle a seulement été déplacée.

Deux pièges qui rendent un résultat faux sans rien signaler. **`-G` lit une expression régulière POSIX
étendue** : `\d` et `\s` n'y existent pas, et git ne se plaint pas, il lit `\d` comme une simple lettre
`d` (vérifié sur git 2.55 : `-G'\d+ skills'` et `-G'd+ skills'` rendent le même commit). On écrit
`[0-9]` et `[[:space:]]`. Et **`-L :fonction:`
trouve les bornes de la fonction avec les règles des en-têtes de diff** : par défaut une heuristique
grossière, et un pilote de langage seulement si `.gitattributes` le déclare (`*.py diff=python`,
`*.cs diff=csharp`). Sans pilote, l'intervalle peut s'arrêter au mauvais endroit.

### Pourquoi ce changement, et qu'est-ce qui a été rejeté ?

```bash
git log --grep='ITEM-142' --oneline            # les commits qui citent un identifiant d'issue
git log --grep='^Revert' --oneline             # les annulations : les zones ou une tentative a echoue
gh pr list --state merged --search "<sha>"     # la PR qui contient ce commit
gh api repos/{owner}/{repo}/commits/<sha>/pulls --jq '.[].html_url'   # idem, par l'API
gh pr view <numero> --comments                 # la discussion : objections, alternatives rejetees
gh api --paginate repos/{owner}/{repo}/pulls/<numero>/comments --jq '.[].body'   # les remarques EN LIGNE du diff
gh issue list --state all --search "<message d'erreur exact>"          # le defaut est-il connu ici ?
gh issue list -R <owner>/<bibliotheque> --state all --limit 100 --search "<message>"   # ... chez la bibliotheque ?
```

### Quand ce comportement a-t-il changé ?

```bash
git bisect start <mauvais> <bon>               # ex. : git bisect start HEAD v1.4.0
git bisect run <commande>                      # code 0 = bon, 125 = a sauter, 1 a 127 = mauvais
git bisect reset                               # toujours, a la fin
```

`bisect run` exige une commande déterministe : un test intermittent fait désigner un commit au hasard.

### Où sont les zones chaudes ?

```bash
# les fichiers les plus souvent modifies sur un an (le "churn")
git log --since="12 months ago" --format=format: --name-only | grep -v '^$' | sort | uniq -c | sort -rn | head -20
```

Un fichier à la fois très modifié et très complexe est l'endroit où les défauts se concentrent
(Adam Tornhill, *Your Code as a Crime Scene*, appelle ça un point chaud). Deux fichiers qui changent
toujours dans les mêmes commits sont couplés, même si aucun n'importe l'autre : c'est une arête
invisible de plus.

## Voir ce qui tourne vraiment, là où la lecture ne suffit pas

Des exemples d'un principe, pas une liste complète : chaque écosystème a son moyen de rendre visible
ce que le code ne dit pas.

| Arête invisible | Ce qui la rend visible (exemples) |
|---|---|
| configuration superposée | la valeur effective à l'exécution : en ASP.NET Core, les sources s'empilent (ligne de commande, variables d'environnement, secrets, `appsettings.{Env}.json`, `appsettings.json`), et la valeur lue peut ne figurer dans aucun fichier ouvert |
| code généré à la compilation | le faire écrire sur le disque : en .NET, `<EmitCompilerGeneratedFiles>true</EmitCompilerGeneratedFiles>` |
| SQL envoyé par un ORM | le journaliser : en EF Core, `optionsBuilder.LogTo(Console.WriteLine)` |
| appels entre services | une trace distribuée : l'instrumentation automatique d'OpenTelemetry suit HTTP, base et files sans toucher au code |
| appels d'une interface web | l'onglet Réseau des outils du navigateur : quelle requête alimente cet écran |

## Les dépendances externes

### Quelle version tourne vraiment ?

| Écosystème | Version résolue | Pourquoi ce paquet est là |
|---|---|---|
| npm | `npm ls <paquet>` | `npm explain <paquet>` |
| .NET | `dotnet list package --include-transitive` | `dotnet nuget why <projet> <paquet>` (SDK récent) |
| Python | `pip show <paquet>` | `pipdeptree -r -p <paquet>` |
| Rust | `cargo tree -i <crate>` | `cargo tree -i <crate>` |
| Go | `go list -m all \| grep <module>` | `go mod why -m <module>` |

### Où est son source, à cette version ?

- Node : `node_modules/<paquet>/`, et le champ `main` ou `exports` de son `package.json` dit quel fichier
  est chargé ;
- Python : `python -c "import <module>, os; print(os.path.dirname(<module>.__file__))"` ;
- Rust : `~/.cargo/registry/src/` ;
- Go : `go env GOMODCACHE` ;
- .NET : aller à la définition avec SourceLink activé, ou un décompilateur (ILSpy, dotPeek).

## Les bases de données

### Quelles tables, quelles colonnes ?

```sql
-- vues du standard SQL, lues par PostgreSQL, SQL Server, MySQL (pas par Oracle ni SQLite)
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_type = 'BASE TABLE'
ORDER BY 1, 2;

SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'orders'
ORDER BY ordinal_position;
```

```bash
psql -c '\d+ orders'                           # PostgreSQL : table, index, contraintes, declencheurs
sqlite3 app.db '.schema orders'                # SQLite
```

Pour un diagramme du schéma réel, des outils l'introspectent et rendent une page ou un graphe
(SchemaSpy, tbls, ce dernier sait sortir du Mermaid) : c'est la règle que `doc-derivee` applique au
diagramme d'architecture, un diagramme dérivé plutôt que dessiné. Une réserve : SchemaSpy **devine**
aussi des relations implicites quand une colonne ressemble à une clé primaire par son nom et son type,
et ces liens-là peuvent être faux.

### Ce que le schéma ne dit pas : les données réelles

```sql
-- quelles valeurs existent VRAIMENT dans une colonne d'etat
SELECT status, COUNT(*) FROM orders GROUP BY status ORDER BY 2 DESC;

-- une colonne nullable est-elle nulle en pratique ?
SELECT COUNT(*) FILTER (WHERE shipped_at IS NULL) AS nulls, COUNT(*) AS total FROM orders;  -- PostgreSQL
```

Toujours en lecture seule, sur une copie hors production quand elle existe, avec un `LIMIT` sur tout
échantillon de lignes.

```sql
EXPLAIN SELECT ...;                            -- le plan, SANS executer : sur n'importe quelle base
BEGIN; EXPLAIN ANALYZE UPDATE ...; ROLLBACK;   -- ANALYZE EXECUTE la requete : copie hors production UNIQUEMENT
```

Même annulée, une écriture mesurée par `EXPLAIN ANALYZE` pose ses verrous, déclenche ses déclencheurs
et consomme ses séquences : elle n'a rien à faire sur une base de production.

### La logique cachée dans la base

```sql
-- PostgreSQL : declencheurs d'une table
SELECT tgname, pg_get_triggerdef(oid) FROM pg_trigger WHERE tgrelid = 'orders'::regclass AND NOT tgisinternal;

-- SQL Server : procedures stockees qui citent une table
SELECT OBJECT_NAME(object_id) FROM sys.sql_modules WHERE definition LIKE '%orders%';
```
