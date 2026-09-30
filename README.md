# LplCraftSkills

Dix-sept skills [Claude Code](https://claude.com/claude-code) indépendantes du langage, qui encodent une façon
de travailler : comprendre avant de décider, décider avant de coder, prouver avant de livrer, et faire
porter par le code tout ce qui pourrait mentir ailleurs.

Elles fonctionnent de deux façons. **Automatiquement** : chaque skill porte une description de
déclenchement, et l'agent la charge quand la tâche y correspond. **À la demande** : taper
`/nom-de-la-skill`.

## Installer

```bash
git clone <ce-depot> LplCraftSkills
cd LplCraftSkills
./install.sh          # un lien par skill dans ~/.claude/skills, les agents artisan et essayeur dans ~/.claude/agents
./install.sh --status # verifier
```

Puis redémarrer la session Claude Code. Le mode par défaut pose des **liens**, jonctions sous Windows,
liens symboliques ailleurs, donc il n'y a **qu'une source de vérité** : éditer dans le dépôt ou dans
`~/.claude/skills` est équivalent. Aucun droit administrateur requis.

Les agents sont la seule exception : ils sont **générés**, pas liés, parce que leurs hooks ont besoin
du chemin absolu du dépôt. Après une modification d'un fichier de `agents/`, relancer `./install.sh` ;
`--status` dit si une copie installée est périmée.

Les autres modes (`--copy`, `--uninstall`) et les codes de sortie : `./install.sh --help`. Ils ne sont pas
listés ici, parce qu'une liste d'options recopiée dans un README finit toujours par mentir, c'est
précisément ce que dit le skill `doc-derivee`.

## Les dix-huit skills

| Skill | En une phrase |
|---|---|
| [`cycle-de-dev`](skills/cycle-de-dev/SKILL.md) | backlog, comprendre l'existant, branche, test, code, doc, PR, revue : chaque étape fermée par une question falsifiable, et le skill à charger à chacune |
| [`explorer-le-code`](skills/explorer-le-code/SKILL.md) | interroger un dépôt inconnu au lieu de le lire : la première heure, un fil suivi de bout en bout, l'histoire d'une ligne |
| [`challenger-le-sujet`](skills/challenger-le-sujet/SKILL.md) | les questions de la revue posées avant elle, par des grilles plutôt que par l'inspiration, puis le fil minimal |
| [`cadrer-et-planifier`](skills/cadrer-et-planifier/SKILL.md) | une spec approuvée section par section, des critères d'acceptation, puis un plan aux tâches calibrées |
| [`concevoir-avant-coder`](skills/concevoir-avant-coder/SKILL.md) | besoin avant solution, YAGNI sur ses deux axes, ossature en stubs, SOLID, injection, modules et paliers de build |
| [`tests-first`](skills/tests-first/SKILL.md) | critères d'acceptation puis tests rouges, et la liste des tests qui mentent |
| [`code-comme-poesie`](skills/code-comme-poesie/SKILL.md) | noms exacts, clauses de garde, aucun commentaire qui paraphrase, doc de contrat |
| [`commencer-ferme`](skills/commencer-ferme/SKILL.md) | déclarer au maximum de contraintes, relâcher sur preuve, avertissements au maximum |
| [`doc-derivee`](skills/doc-derivee/SKILL.md) | un `--help` complet plutôt qu'un README qui mentira, sortie machine pure, erreurs auto-descriptives |
| [`journal-et-debogueur`](skills/journal-et-debogueur/SKILL.md) | journal structuré et débogueur en une touche, installés au jour 1 ; assertions et modes de build |
| [`trouver-la-cause`](skills/trouver-la-cause/SKILL.md) | pas de correctif sans cause racine, et les correctifs qui masquent au lieu de corriger |
| [`mesure-et-telemetrie`](skills/mesure-et-telemetrie/SKILL.md) | un banc est un test de non-régression sur une grandeur continue ; télémétrie et artefact de production |
| [`rendre-l-etat-visible`](skills/rendre-l-etat-visible/SKILL.md) | quand l'information est dans la forme, on la rend visible, et le même artefact habille la doc |
| [`se-faire-comprendre`](skills/se-faire-comprendre/SKILL.md) | le lecteur, le message en une phrase, la réponse d'abord, l'exemple avant l'explication, le visuel cadré, un lecteur froid |
| [`tracer-le-travail`](skills/tracer-le-travail/SKILL.md) | backlog, commits, versionnement, changelog, PR, revue, porte de merge |
| [`relire-une-pr`](skills/relire-une-pr/SKILL.md) | relire la PR d'un autre sans rien publier : la CI avant le diff, la description comme des affirmations, les états que le diff ne montre pas, une passe hostile |
| [`garder-les-frontieres`](skills/garder-les-frontieres/SKILL.md) | la sécurité comme une question posée quand un changement touche une frontière de confiance, puis l'escalade vers l'équipe sécurité, jamais un feu vert auto-décerné |
| [`tenir-la-forge`](skills/tenir-la-forge/SKILL.md) | un dépôt et son board tenus par un fichier déclaré et un outil qui montre son plan : des étiquettes fermées, une vue par question, les règles d'un mainteneur seul, la sécurité gratuite d'un dépôt public |

## Le fil rouge, en trois idées

Tout le reste en découle.

1. **Une affirmation doit être falsifiable, et elle se prouve avant de se dire.** « Le code est propre »
   ne l'est pas ; « la suite passe deux fois de suite sans nettoyage manuel » l'est. Et on ne déclare pas
   un état sans avoir lancé, à l'instant, la commande qui le prouve : « ça devrait marcher » n'est pas un
   résultat.
2. **Ce qui peut être dérivé ne doit pas être écrit à la main.** Un texte écrit à côté d'un code finit
   toujours par mentir, et rien ne casse. Donc : générer, ou apparier par un test, ou écrire où ça peut
   mentir.
3. **Élargir est gratuit, resserrer casse tout le monde.** D'où le réflexe de commencer fermé, sur une
   visibilité, un qualifieur, un point d'extension, et de relâcher comme un acte volontaire.

## Ordre de lecture

**Si tu débutes en programmation**, dans cet ordre, un skill à la fois :

1. **`cycle-de-dev`**, la carte. Elle situe tout le reste ;
2. **`tests-first`**, le geste le plus contre-intuitif et le plus payant : écrire le test avant le code ;
3. **`code-comme-poesie`**, applicable à la ligne suivante que tu écris ;
4. **`journal-et-debogueur`, partie 2 d'abord**, le débogueur en une touche. C'est là qu'un débutant perd
   le plus de temps, à chercher au `printf` ce qu'un point d'arrêt montre en dix secondes ;
5. **`trouver-la-cause`**, dans la foulée : l'outil sans la méthode ne suffit pas, et « corriger un
   symptôme est un échec » est la leçon qui coûte le plus cher à apprendre seul ;
6. **`explorer-le-code`, sections 1 à 3**, avant ta première contribution à un projet partagé : un
   dépôt que tu n'as pas écrit s'interroge, il ne se lit pas de haut en bas ;
7. **`tracer-le-travail`, sections 1 à 3**, backlog, branche, commits. Ce que tu rencontres dès cette
   première contribution ;
8. **`concevoir-avant-coder`**, quand tu auras assez de code pour que les abstractions te mordent.

Deux skills sortent du code et se lisent dès qu'un rapport, un audit, un exposé ou une revue arrive,
quel que soit ton niveau : **`challenger-le-sujet`** et **`se-faire-comprendre`**. Elles vont par paire :
on ne choisit bien l'essentiel à dire que parmi tout ce qu'on sait.

Trois autres se lisent au premier événement qui les appelle : **`relire-une-pr`** la première fois qu'on
te demande de relire la PR de quelqu'un, **`garder-les-frontieres`** la première fois qu'un changement
touche une entrée, un secret, une permission ou une dépendance, et **`tenir-la-forge`** la première
fois que tu crées un dépôt, que tu l'ouvres au public ou que tu montes un board.

Les cinq autres (`cadrer-et-planifier`, `commencer-ferme`, `doc-derivee`, `mesure-et-telemetrie`,
`rendre-l-etat-visible`) répondent à des problèmes qu'il faut avoir rencontrés pour que la réponse ait du
sens. Elles attendront.

**Si tu es déjà développeur** : lis `cycle-de-dev` pour la carte, puis va directement au skill du
problème que tu as. Chacune se lit seule.

Cet ordre sert à **apprendre**, et ce n'est pas l'ordre dans lequel on s'en sert. L'ordre d'exécution,
étape par étape et avec le skill à charger à chaque étape, est le cycle de `cycle-de-dev` : c'est lui
que suit l'agent `artisan`.

## L'agent `artisan` : les skills appliqués par des rails

Pour qu'une session de Claude Code travaille selon ce pack sans qu'on le lui rappelle :

```bash
claude --agent artisan
```

L'agent ([`agents/artisan.md`](agents/artisan.md)) ne recopie aucun skill. Il dit quand charger lequel :
`cycle-de-dev` d'abord, puis le skill de chaque étape au moment où elle arrive, et la porte de sortie de
chacun prouvée par une commande avant de conclure. Charger les dix-huit d'avance coûterait environ
100 000 jetons et noierait la règle utile au moment où elle sert.

Deux règles ne dépendent pas de sa bonne volonté, parce que ce sont des hooks
([`agents/hooks/artisan-gate.cjs`](agents/hooks/artisan-gate.cjs)) :

- **aucune écriture avant la carte** : `Edit` et `Write` sont refusés tant que `cycle-de-dev` n'a pas
  été chargé. Lire et explorer restent permis ;
- **aucun arrêt sur une écriture non prouvée** : un fichier modifié après la dernière commande fait
  refuser le premier arrêt, une fois. Le hook sait qu'une commande a tourné, pas que c'était la bonne.

Les hooks demandent `node`. Et l'agent doit vivre au niveau utilisateur, là où `install.sh` le pose :
dans le `.claude/agents/` d'un projet, ses hooks ne se déclenchent pas. C'est mesuré, comme le reste
de ce que la documentation de Claude Code ne dit pas, par
[`forgeron/tests/probes/probe_claude_agent.sh`](forgeron/tests/probes/probe_claude_agent.sh).

## L'agent `essayeur` : relire sans rien publier

```bash
claude --agent essayeur
```

L'agent ([`agents/essayeur.md`](agents/essayeur.md)) relit une pull request ou un diff et rend un
rapport. Il n'approuve pas, ne corrige pas et ne publie rien : la décision appartient à l'humain qui
lit le rapport. Son nom vient du métier : l'essayeur teste l'alliage d'une pièce qu'il n'a pas forgée,
et ce n'est pas lui qui pose le poinçon.

Il sert de deux façons. **Lancé par une personne**, sur la PR d'un collègue. **Lancé par l'`artisan`**,
avant la revue humaine, quand se tromper coûte cher : l'auteur ne se relit pas lui-même, parce qu'il
relit avec son contexte en tête. Le relecteur séparé n'a pas sa conversation, donc il voit ce que ce
contexte masque.

Ses règles sont tenues par un hook ([`agents/hooks/essayeur-gate.cjs`](agents/hooks/essayeur-gate.cjs)) :

- **aucun outil d'écriture** : ils sont absents de sa liste et refusés s'ils reviennent. Le rapport est
  sa réponse finale. Une commande peut encore écrire, donc les builds et les linters se lancent dans son
  worktree ;
- **aucune publication, aucun changement d'état d'un dépôt** : les commandes `gh` qui ne sont pas des
  lectures connues, les `gh api` qui écrivent, les commandes git autres que les lectures, `fetch`,
  `clone`, `init`, `worktree add` et `worktree list`, les envois de données par `curl`, `wget`,
  `Invoke-RestMethod` ou `Invoke-WebRequest`, et les publications de paquets sont refusés avant de
  partir. Les listes de lectures permises sont fermées : un verbe inconnu, ou une forme de commande que
  le rail ne reconnaît pas, est refusé ;
- **un sous-agent est un essayeur, un skill vient du pack** : un autre type d'agent, ou un skill
  d'ailleurs, n'aurait pas ces rails.

Le rail attrape l'accident, pas la volonté de le contourner. Et son hook tire aussi quand il tourne en
**sous-agent**, pas seulement en session : c'est mesuré, avec Claude Code 2.1.259, par
[`forgeron/tests/probes/probe_claude_subagent.sh`](forgeron/tests/probes/probe_claude_subagent.sh).

## `forgeron/` — les skills appliquées sans surveillance

[`forgeron/`](forgeron/README.md) est une **preuve de concept**, à part des skills : un pilote local
qui écoute les issues GitHub étiquetées, ouvre une pull request en brouillon avant d'écrire une
ligne, code en suivant ces skills, attend l'intégration continue, demande la revue, et boucle sur
tes commentaires jusqu'à ce que tu fusionnes.

Elle est ici parce que c'est le pack qu'elle applique, et elle est dans son propre dossier parce
que ce pack **ne prescrit pas d'outillage** : `forgeron` est un exemple d'un principe, pas une
recommandation. Rien dans `skills/` n'en dépend, et les skills se lisent sans elle.

Python 3, `git`, `gh`, `claude`. Aucune infrastructure, aucun jeton à copier.

```bash
cd forgeron && ./tests/run.sh
```

## Conventions

- **chaque skill se termine par une « porte de sortie »** : la liste des réponses qui doivent exister avant
  de passer à la suite. C'est la partie à relire, et la seule à relire si on est pressé ;
- **les dossiers `references/`** contiennent le détail copiable, configurations, commandes, catalogues. Ils
  ne se lisent pas d'affilée : on y va quand le skill y renvoie ;
- **les schémas sont en Mermaid**, jamais en art ASCII. Les rares blocs de texte qui ressemblent à des
  schémas sont des **exemples de sortie**, c'est le sujet, pas de la décoration ;
- **le texte des schémas est en anglais**, et la prose autour en français. Sur GitHub, un schéma Mermaid
  devient une image, que la traduction du navigateur ne traduit pas : un lecteur qui ne lit pas le
  français comprend la prose traduite, et il doit pouvoir lire le schéma aussi ;
- **la ponctuation suit la typographie française** : une espace insécable avant `;` `:` `!` `?` et à
  l'intérieur des guillemets « », hors des blocs de code ;
- **la prose est accentuée, les commentaires dans les blocs de code ne le sont pas** : ces blocs sont
  destinés à être copiés dans des sources et des configurations, où un problème d'encodage coûterait plus
  que le confort de lecture.

Et ces conventions ne sont pas seulement écrites, elles sont **vérifiées** :

```bash
./check.sh   # les portes de sortie, les frontmatters, le tableau ci-dessus, l'absence d'art ASCII,
             # la carte des agents (chacun nomme tous les skills), les tests de leurs hooks
             # et les espaces insécables de la prose
```

Il existe parce que trois skills avaient perdu leur porte de sortie sans que personne ne le remarque :
ce README l'affirmait, et rien ne le contredisait. Une affirmation invérifiable finit toujours par être
fausse, ce qui est exactement le fil rouge du pack, appliqué au pack.

## Ce que ce pack ne fait pas

- **il n'apprend aucun langage.** Il suppose que tu sais écrire une fonction ; il parle de ce qu'on fait
  autour ;
- **il ne prescrit pas d'outillage.** Les outils cités sont des exemples d'un principe, jamais une
  recommandation. Le principe survit à l'outil ;
- **il ne tranche pas ce qui dépend du contexte : il donne le critère.** Trois sujets y sont explicitement
  à deux réponses : le backlog en fichiers ou en issues de forge, le versionnement par contrat ou par
  cadence, et la fermeture d'une pull request en squash ou en commit de fusion. Dans les trois cas, le
  skill donne la question qui décide plutôt qu'un verdict ;
- **il n'est pas une étude.** C'est de l'expérience condensée : des règles qui ont chacune été payées par
  une panne, pas un résultat mesuré sur une population de projets. Quand une règle s'appuie sur une
  étude, elle la cite avec son auteur et son année, pour qu'on puisse la vérifier. Le reste est à lire
  comme un avis argumenté, et à contredire par une mesure si tu en as une. C'est d'ailleurs ce que le
  pack demande partout ailleurs.
