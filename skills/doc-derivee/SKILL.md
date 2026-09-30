---
name: doc-derivee
description: >-
  Fait porter la documentation par la surface elle-meme plutot que par de la prose a cote : un
  `--help` complet et relu comme un livrable, une surface qui varie selon le palier de build, une
  sortie machine (`--json`) pure, des messages d'erreur auto-descriptifs, des verbes de lecture pour
  relire ce que l'outil produit, et de la doc generee ou apparie par un test quand elle reste en
  prose. Porte aussi la carte des artefacts : quel support repond a quelle question (README, --help,
  CHANGELOG, CONTRIBUTING, doc de contrat, backlog, wiki), la frontiere entre se servir d'un projet et
  le changer, le critere qui decide de ce qui va dans un wiki, et le sort d'un fichier destine a un
  agent. A utiliser pour ecrire ou relire un README, concevoir une
  surface de CLI ou d'API, ajouter une option, rediger un message d'erreur, arbitrer ou une
  information doit vivre, ou quand une doc est perimee sans que rien ne l'ait signale.
---

# La doc dérivée, celle que personne n'écrit deux fois

*En une phrase : ce qui peut être généré depuis le code ne doit pas être écrit à la main, parce que
tout texte écrit à la main finit par mentir sans que rien ne casse.*

Un compilateur casse quand une signature change ; un paragraphe ne casse jamais. C'est pour ça qu'un
README qui liste les options est périmé avant d'être relu, alors qu'un `--help` généré depuis la
déclaration des options ne peut pas l'être.

La réponse n'est pas la discipline, elle échoue toujours à la longue. Elle est structurelle :
**DÉRIVER** ce qui peut l'être, **APPARIER** par un test ce qui reste, et **ÉCRIRE L'ÉCART** quand ni
l'un ni l'autre n'est possible.

## L'échelle de fiabilité

Chaque descente d'un cran ajoute une chose qui peut mentir **sans que rien ne casse**.

| Cran | Support | Peut-il mentir ? |
|---|---|---|
| 1 | le code, les types, les noms | non, c'est lui qui s'exécute |
| 2 | le `--help` généré depuis la déclaration des options | non, même source que l'analyseur d'arguments |
| 3 | la doc d'API générée depuis les signatures | partiellement : la prose des descriptions peut dériver |
| 4 | l'exemple **exécuté**, test de documentation, exemple joué en intégration continue | non tant qu'il tourne : il casse quand il mente |
| 5 | le README **apparié** par un test, dont les commandes sont extraites et jouées | il casse quand il mente |
| 6 | le README libre | oui, et **silencieusement** |

Le geste utile n'est pas « écrire moins de doc », c'est **monter d'un cran** chaque fois que c'est
possible. Une page de prose qui liste des options fait descendre au cran 6 quelque chose qui vivait au
cran 2.

## La carte des artefacts : deux axes, pas un

Le blocage habituel vient de ce qu'on trie par **public** (les utilisateurs, les développeurs, tout le
monde) alors que l'échelle ci-dessus trie par **fiabilité**. Les deux axes sont réels et orthogonaux :
un artefact se place au croisement de *à qui il répond* et de *à quel cran il peut mentir*.

| Qui, et sa question | Artefact | Cran |
|---|---|---|
| n'importe qui, en cinq minutes : à quoi ça sert, comment j'obtiens un premier résultat | le README | 5, si un test joue ses commandes |
| celui qui s'en sert : quelles options, quels codes de sortie, quels formats | le `--help` | 2 |
| celui qui met à jour : qu'est-ce qui va m'arriver | le CHANGELOG, dérivé des commits (forme dans `tracer-le-travail`) | 2 |
| celui qui appelle : qu'exige cette fonction, que garantit-elle | la doc de contrat sur la frontière publique (voir `code-comme-poesie`) | 3 |
| celui qui modifie : comment ça marche | **le code** | 1 |
| celui qui contribue : comment on nomme, on commit, ce qui bloque un merge | le CONTRIBUTING | 5, et chaque convention qui devient un contrôle monte au cran 2 |
| celui qui décide de la suite : qu'est-ce qui est prévu, priorisé, bloqué | le backlog, un seul (sa question qui décide est dans `tracer-le-travail`) | selon le support |
| celui qui demande POURQUOI : pourquoi ce choix, pourquoi pas l'autre | le wiki | daté, donc n'expire pas |

**Aucune ligne ne se répète, et c'est le test de la carte.** Si deux artefacts répondent à la même
question, l'un des deux mentira, et ce sera celui que personne ne relit. Le cas le plus courant est un
fichier de feuille de route à côté d'un backlog de forge déjà priorisé : la forge porte l'état, le
fichier porte l'intention d'il y a six mois, et rien ne signale l'écart.

Cette carte dit **où** vit une information. **Comment** l'écrire pour qu'elle soit comprise (le
lecteur, le message en une phrase, la réponse d'abord, l'exemple avant l'explication) est dans
`se-faire-comprendre`.

Les deux lignes qu'on confond le plus sont le README et le CONTRIBUTING, et la frontière est nette :
le premier sert à **se servir** du projet, le second à **le changer**. Un lecteur qui veut un résultat
n'a rien à faire d'un format de message de commit, et un contributeur n'a pas besoin qu'on lui
re-explique à quoi sert le projet.

### Le wiki n'a pas de public à lui, d'où la difficulté à le remplir

Tous les publics de la carte sont déjà servis. Ce qui reste au wiki est une **question** que rien
d'autre ne porte, et le critère qui décide est celui du temps grammatical :

> **Le wiki accueille ce qui porte une DATE, pas un ÉTAT.**

Une décision datée ne peut pas devenir fausse : elle n'a jamais prétendu décrire maintenant. Une
description du présent expire, et elle expire **en silence**, parce qu'un wiki vit hors du dépôt, donc
hors de la revue et hors de portée de tout test. C'est l'anti-pattern listé plus bas, et c'est la
même raison qui rend le wiki parfait pour le premier usage et interdit pour le second.

Y vont donc les décisions d'architecture avec ce qui a été **rejeté** et pourquoi, les leçons payées
avec leur signature et leur remède, et le long-form daté : une étude de performance avec sa machine et
sa date, un chapitre, un rapport.

**Deux choses n'y vont pas, dont une qui s'y invite toujours.** Les commandes d'installation
**restent dans le README**, parce que là un test peut les extraire et les jouer : les déplacer les fait
passer du cran 5 au cran 6 et supprime le seul mécanisme capable de voir qu'elles mentent. Et l'état
présent ne s'y écrit pas, il **se génère**. Une liste de modules tenue à la main est la page qui
mentira la première et le plus vite, puisque c'est celle dont la vérité change à chaque ajout.

### Les visuels sont des artefacts, pas de la décoration

Leur règle vit dans `rendre-l-etat-visible` et elle vaut ici sans changement : tout visuel qui part
dans une doc porte **la commande qui le régénère**, sinon c'est une capture d'écran et elle mentira en
silence. Ça pèse d'autant plus dans un README, où une image ou une animation est à la fois le contenu
le plus utile et le plus périssable qui existe : elle montre une interface, une commande et une sortie,
et les trois bougent. Un diagramme d'architecture se **dérive** du graphe de dépendances plutôt que de
se dessiner, ce qui le fait monter du cran 6 au cran 2.

## Le fichier destiné à un agent

Un document écrit pour un agent est au cran 6 **sans public humain**, ce qui est la pire case de la
grille : rien ne le relit, donc rien ne le contredit, donc il grossit. Un fichier de contexte de
plusieurs milliers de lignes est le produit normal d'une prose dont le seul lecteur ne l'ouvrira
jamais en entier, et il est chargé automatiquement, donc son coût est payé à chaque
session.

**La question à poser porte sur ce qui a besoin d'y être, avant celle de sa longueur.** Trier son
contenu ligne à ligne donne un résultat contre-intuitif : presque rien.

| ce qu'on y trouve | où ça va vraiment |
|---|---|
| une convention de nommage, un format de commit, une exigence de signature | le CONTRIBUTING, qu'un humain qui contribue lit, donc qui est relue |
| un piège d'outillage, du genre « telle commande ne construit rien » ou « le code de sortie d'un pipeline est celui de sa dernière commande » | un **contrôle** s'il est vérifiable, le CONTRIBUTING sinon. tout contributeur le rencontre, un humain compris |
| une règle que la machine applique déjà, du genre « ne pas commiter ce dossier » | rien, le fichier d'exclusion la porte déjà et la prose est un doublon |
| l'historique des décisions | le wiki, daté |
| la carte du projet | le README |

Ce qui reste après le tri tient à une seule question : **qui applique la borne.** Un agent qui
contribue à travers la forge occupe le siège du contributeur externe, et un contributeur externe n'a
besoin d'aucun document pour savoir qu'il ne poussera pas sur la branche d'intégration : la forge le
lui refuse. Sa borne n'est écrite nulle part, elle est structurellement infranchissable.

Donc « ne pousse jamais sur la branche d'intégration » dans un fichier d'agent est au cran 6, quand la
même règle en protection de branche est au cran 1, le serveur refusant le push. Toute interdiction
qu'on s'apprête à écrire dans un fichier d'agent commence par la question de savoir si le modèle de
permissions peut la porter, et la plupart peuvent.

Ce que les permissions ne savent pas exprimer reste dans le CONTRIBUTING, parce que ça vaut pour tout
contributeur. « On ne réécrit pas l'historique d'une branche que quelqu'un est en train de relire » ne
peut pas devenir une protection sans interdire du même coup le rebase légitime après un conflit, et
c'est une règle qui s'adresse autant à un humain.

**Et un agent qui tourne avec les identifiants du mainteneur n'occupe pas ce siège**, quoi qu'en dise
son prompt : il détient l'accès en écriture de la personne qu'il est censé assister, donc chacune de
ses bornes redevient une phrase. Ce qui rend le rôle réel est une identité propre, avec sa propre
installation aux permissions restreintes. Un document mieux rédigé n'y change rien. Après ça, un
fichier d'agent ne porte que ce que la forge ne sait pas représenter, et il est plausible qu'il ne
reste rien.

Un fichier de délégation fait une dizaine de lignes. **Un fichier d'agent qui grossit est donc un
symptôme mesurable** : compter dedans les pièges notés comme re-payés donne le nombre de contrôles
qui n'ont pas été écrits, et compter ses conventions donne la taille du CONTRIBUTING qui manque.

Le test de taille est celui du lecteur : **ce que tu ne relis pas, un agent ne le lira pas non plus,
il l'échantillonnera.**

## Ce que le README garde, et ce qu'il doit rendre

Le README n'est pas une référence, c'est une **porte d'entrée**. Quatre choses, qu'aucun `--help` ne
peut porter :

1. **pourquoi ce projet existe**, et le problème qu'il résout ;
2. **démarrer en cinq minutes** : la seule séquence de commandes qui mène à un premier résultat ;
3. **où vivent les choses** : la carte, pas le détail ;
4. **ce que le projet REFUSE de faire**, et pourquoi. La section la plus utile et la plus rare, parce
   que c'est celle qui empêche la même question de revenir tous les quinze jours.

Ce qu'il doit rendre au `--help` : la liste des options, leurs valeurs par défaut, les codes de sortie,
la référence des sous-commandes. **Écrire « voir `<outil> --help` » est une réponse complète**, et c'est
la seule qui reste vraie.

## Un `--help` bien fait : c'est un livrable, pas un effet de bord

Il se relit en revue, comme du code. Le contenu obligatoire :

| Élément | Pourquoi il manque presque toujours |
|---|---|
| **synopsis** | on suppose que la forme est évidente |
| **ce que la commande FAIT DU MONDE** : lit, écrit, dépense du temps, touche un système distant | c'est la seule information qui évite un appel destructeur par curiosité |
| **les valeurs par défaut, VISIBLES** | sans elles, l'utilisateur ne peut pas savoir ce qui arrive s'il ne choisit pas |
| **d'où viennent la configuration et les fichiers lus** | la première question de tout débogage : « il a lu quel fichier ? » |
| **les codes de sortie**, un par cause | c'est ce qui rend l'outil scriptable ; sans ça, l'appelant analyse le texte |
| **deux ou trois exemples COPIABLES** qui tournent vraiment | un exemple faux coûte plus cher que pas d'exemple |
| **où va la sortie** : écran, fichier, dossier d'artefacts | sinon l'utilisateur cherche son résultat |

Et la règle de dérivation : **le contenu d'un `--help` se relève sur le binaire, jamais recopié en
prose.** Quand une doc doit citer la surface, elle cite ce que la commande **répond**, pas ce dont on se
souvient. Un tableau d'options recopié à la main est un duplicata avec une horloge : il annoncera vingt-six
verbes le jour où il y en aura trente, et personne ne le verra.

> **Le test qui attrape ça** : lancer `<outil> --help` et comparer à ce que la doc affirme. S'ils
> divergent, c'est la doc qui a tort, par construction.

## Quand la surface VARIE selon le palier de build

Si l'artefact existe en paliers (prod, dev, debug, voir `concevoir-avant-coder`), toutes les commandes
ne sont pas présentes partout. C'est le meilleur révélateur de ce skill : **une aide dérivée des
verbes réellement enregistrés est juste dans chaque palier sans un geste de plus**, tandis qu'une aide
écrite à la main se met à mentir **dès le premier palier**, en annonçant ce que le binaire ne contient
pas. Les paliers ne cassent pas la doc dérivée : ils cassent l'autre.

Quatre règles, et l'asymétrie de la deuxième est le point important :

1. **`--help` liste ce que CE build sait faire**, parce qu'il est généré depuis les verbes réellement
   enregistrés. Le README, lui, ne les énumère pas : il renvoie au `--help`. Sinon il faudrait N listes
   écrites à la main, une par palier, et elles divergeraient toutes ;
2. **absent de l'aide mais fonctionnel** est tolérable si c'est **délibéré**, une surface de
   compatibilité : anciens noms, alias, à condition qu'un test verrouille **les deux** formes.
   **Listé dans l'aide mais indisponible est un défaut**, toujours. Les deux erreurs ne se valent pas :
   la première surprend agréablement, la seconde fait échouer quelqu'un qui a suivi la doc ;
3. **un verbe absent de CE palier ne répond pas « commande inconnue ».** C'est la règle « nommer les
   endroits regardés » appliquée aux paliers :

   ```
   # inutile, et faux : la commande existe
   error: unknown command 'specs'

   # utile
   Erreur: 'specs' existe mais n'est pas inclus dans ce build (outils de dev exclus).
   Ce build expose: generate, seed. Pour les outils de lecture: build de dev.
   ```

4. **`--version` dit de quel palier il s'agit** : `1.4.0 (release, sans outils de dev)`. Sans ça, un
   rapport de bug ne permet pas de savoir quel programme a tourné, et on débogue le mauvais. C'est deux
   lignes, et ça sert précisément dans le palier que personne n'exerce à la main.

## La sortie machine, et la règle qui la rend utilisable

Un mode `--json`, `--porcelain` ou `--format=...` n'est pas cosmétique : **c'est ce qui permet de
composer une mesure sans réécrire un motif à la main.** Or un motif écrit à la main n'est pas une mesure,
c'est une devinette qui renvoie un nombre plausible.

**Une sortie machine ne partage JAMAIS son flux avec un diagnostic.** La sortie standard porte la
réponse, la sortie d'erreur porte tout le reste, avertissement, progression, troncature. Une seule
ligne de diagnostic au mauvais endroit et l'analyse de l'appelant échoue : le mode machine devient
inutilisable, donc l'appelant repart au motif écrit à la main, donc on ramène le problème par la porte de
derrière.

Deux pièges qui se ressemblent et se paient pareil :

- **une sous-commande qui ignore `--json` en silence.** Pire qu'absent : l'appelant ne le découvre qu'à
  l'analyse ;
- **un `--json` qui n'est testé sur aucun mode.** Le test qui vaut : **tous** les modes machine doivent
  s'analyser, diagnostics compris. Avec un plancher, s'il n'y a plus aucun mode à tester, le test doit
  refuser de passer au vert.

## Si ton outil produit des artefacts, il doit savoir les relire

Un outil qui **écrit** des journaux, des rapports, des mesures, et qui n'offre **aucune façon de les
relire**, force chaque utilisateur à écrire son propre filtre. Ce n'est pas une gêne, c'est une
multiplication : sur un projet réel, ce défaut précis a produit **89 scripts ad hoc**, chacun avec son
propre périmètre, dont plusieurs faux sans que personne le sache.

La règle : **pour chaque famille d'artefacts produite, un verbe de lecture**, hors ligne, qui ne touche
rien et qui sait rendre du machine. Ce qui remonte alors du même coup : les périmètres divergents, les
fichiers tronqués, les lectures qui rendaient zéro parce qu'elles cherchaient au mauvais endroit. **Un
zéro et « je n'ai pas regardé » sont deux réponses différentes**, et seul un lecteur explicite peut les
distinguer.

## Les messages d'erreur sont de la doc, au moment exact où elle sert

C'est la documentation la plus lue d'un outil, et la moins écrite. Un bon message porte trois choses :
**quoi** (la valeur, pas la catégorie), **où** (le fichier, la ligne, l'identifiant) et **quoi
faire**.

```
# inutile
Error: invalid configuration

# utile
Erreur: 'timeoutMs' vaut -1 dans C:/app/config.local.json (ligne 12).
Attendu: un entier > 0. Valeur par defaut si absent: 30000.
```

Et quand une recherche échoue, **nommer les endroits regardés**. « Fichier introuvable » lance une
enquête ; « introuvable, cherché dans A, B, C » la termine.

## Ce qui reste en prose : dériver, apparier, ou écrire l'écart

- **dériver** : générer la page depuis la source qui fait autorité, signatures, déclarations d'options,
  schéma ;
- **apparier** : un test compare la prose à sa source. Extraire les blocs de commandes du README et les
  **exécuter** en intégration continue est l'appariement le plus rentable qui existe : il attrape les
  exemples périmés, première cause de perte de confiance dans une doc ;
- **écrire l'écart** : quand ni l'un ni l'autre n'est possible, dire dans le document **où il peut
  mentir**. Un document qui annonce ses zones aveugles vaut infiniment mieux qu'un document qu'on croit
  exact.

## Par écosystème, où vit la dérivation

| Besoin | C / C++ | C# / .NET | TypeScript / Node | Rust | Python |
|---|---|---|---|---|---|
| options vers `--help` | `getopt`, CLI11, cxxopts | System.CommandLine | commander, yargs, oclif | clap (dérivé) | argparse, click, typer |
| signatures vers doc | Doxygen | XML doc + DocFX | TypeDoc | rustdoc | Sphinx |
| exemple **exécuté** | tests et extraits compilés en CI | exemples compilés | exemples en CI | **doctests rustdoc** (natif) | **doctest** (natif) |

Rust et Python ont l'exemple exécuté **en standard** : c'est le cran 4 gratuitement. Ailleurs il se
construit, et ça vaut le coup, parce que c'est le seul cran où un exemple faux **casse le build**.

## Anti-patterns, avec leur signature

- **le README qui documente les options.** Signature : il annonce un nombre d'options différent de ce que
  `--help` liste. Toujours dans le sens « le README en oublie » ;
- **le `--help` généré mais jamais relu.** Signature : un mur de drapeaux, aucun exemple, aucune valeur
  par défaut visible. Dérivé donc exact, et inutilisable ;
- **la doc qui vit dans un wiki.** Signature : elle ne bouge pas quand le code bouge, parce qu'elle n'est
  pas dans la revue. Ce qui n'est pas dans le dépôt n'est pas dans le cycle ;
- **l'exemple non exécuté.** Signature : il utilise un drapeau renommé il y a six mois. C'est le plus
  coûteux, parce qu'il fait perdre confiance dans **toute** la doc et pas seulement dans ce bloc ;
- **la mesure par filtre écrit à la main.** Signature : un motif recopié de mémoire, un nombre plausible,
  et personne pour le contredire. C'est le symptôme d'une sortie machine absente ou impure.

## La porte de sortie

Avant de publier l'outil, ces six réponses doivent exister :

1. le `--help` a été **relu comme un livrable** : il porte au moins un exemple, il montre les valeurs par
   défaut, et il se lit sans connaître le code ;
2. le README **ne recopie aucune option**. Ce qu'il garde, c'est ce que `--help` ne peut pas dire : à quoi
   sert l'outil, et par où commencer ;
3. la sortie machine est **pure**, rien d'autre ne sort sur le canal de sortie, et une commande la lit
   sans qu'un humain ait à découper du texte ;
4. les artefacts que l'outil produit, il sait **les relire** : un verbe qui les inspecte existe, sinon la
   seule façon de vérifier une sortie est de la croire ;
5. chaque message d'erreur dit **quoi, où, et comment en sortir**, à l'endroit exact où le lecteur en a
   besoin ;
6. ce qui reste en prose est **apparié par un test**, généré, ou l'écart est écrit avec la condition de
   son retrait.

Et le geste qui résume le skill : **monter d'un cran sur l'échelle, pas écrire moins de doc.** Une page
qui liste des options fait descendre au cran 6 quelque chose qui vivait au cran 2, et le cran 6 est le
seul où un texte peut mentir sans que rien ne casse.
