---
name: doc-derivee
description: >-
  Fait porter la documentation par la surface elle-meme plutot que par de la prose a cote : un
  `--help` complet et relu comme un livrable, une surface qui varie selon le palier de build, une
  sortie machine (`--json`) pure, des messages d'erreur auto-descriptifs, des verbes de lecture pour
  relire ce que l'outil produit, et de la doc generee ou apparie par un test quand elle reste en
  prose. A utiliser pour ecrire ou relire un README, concevoir une surface de CLI ou d'API, ajouter
  une option, rediger un message d'erreur, ou quand une doc est perimee sans que rien ne l'ait
  signale.
---

# La doc dérivée, celle que personne n'écrit deux fois

*En une phrase : ce qui peut être généré depuis le code ne doit pas être écrit à la main, parce que
tout texte écrit à la main finit par mentir sans que rien ne casse.*

Un compilateur casse quand une signature change ; un paragraphe ne casse jamais. C'est pour ça qu'un
README qui liste les options est périmé avant d'être relu, alors qu'un `--help` généré depuis la
déclaration des options ne peut pas l'être.

La réponse n'est pas la discipline, elle échoue toujours à la longue. Elle est structurelle :
**DÉRIVER** ce qui peut l'être, **APPARIER** par un test ce qui reste, et **ÉCRIRE L'ÉCART** quand ni
l'un ni l'autre n'est possible.

## L'échelle de fiabilité

Chaque descente d'un cran ajoute une chose qui peut mentir **sans que rien ne casse**.

| Cran | Support | Peut-il mentir ? |
|---|---|---|
| 1 | le code, les types, les noms | non, c'est lui qui s'exécute |
| 2 | le `--help` généré depuis la déclaration des options | non, même source que l'analyseur d'arguments |
| 3 | la doc d'API générée depuis les signatures | partiellement : la prose des descriptions peut dériver |
| 4 | l'exemple **exécuté**, test de documentation, exemple joué en intégration continue | non tant qu'il tourne : il casse quand il mente |
| 5 | le README **apparié** par un test, dont les commandes sont extraites et jouées | il casse quand il mente |
| 6 | le README libre | oui, et **silencieusement** |

Le geste utile n'est pas « écrire moins de doc », c'est **monter d'un cran** chaque fois que c'est
possible. Une page de prose qui liste des options fait descendre au cran 6 quelque chose qui vivait au
cran 2.

## Ce que le README garde, et ce qu'il doit rendre

Le README n'est pas une référence, c'est une **porte d'entrée**. Quatre choses, qu'aucun `--help` ne
peut porter :

1. **pourquoi ce projet existe**, et le problème qu'il résout ;
2. **démarrer en cinq minutes** : la seule séquence de commandes qui mène à un premier résultat ;
3. **où vivent les choses** : la carte, pas le détail ;
4. **ce que le projet REFUSE de faire**, et pourquoi. La section la plus utile et la plus rare, parce
   que c'est celle qui empêche la même question de revenir tous les quinze jours.

Ce qu'il doit rendre au `--help` : la liste des options, leurs valeurs par défaut, les codes de sortie,
la référence des sous-commandes. **Écrire « voir `<outil> --help` » est une réponse complète**, et c'est
la seule qui reste vraie.

## Un `--help` bien fait : c'est un livrable, pas un effet de bord

Il se relit en revue, comme du code. Le contenu obligatoire :

| Élément | Pourquoi il manque presque toujours |
|---|---|
| **synopsis** | on suppose que la forme est évidente |
| **ce que la commande FAIT DU MONDE** : lit, écrit, dépense du temps, touche un système distant | c'est la seule information qui évite un appel destructeur par curiosité |
| **les valeurs par défaut, VISIBLES** | sans elles, l'utilisateur ne peut pas savoir ce qui arrive s'il ne choisit pas |
| **d'où viennent la configuration et les fichiers lus** | la première question de tout débogage : « il a lu quel fichier ? » |
| **les codes de sortie**, un par cause | c'est ce qui rend l'outil scriptable ; sans ça, l'appelant analyse le texte |
| **deux ou trois exemples COPIABLES** qui tournent vraiment | un exemple faux coûte plus cher que pas d'exemple |
| **où va la sortie** : écran, fichier, dossier d'artefacts | sinon l'utilisateur cherche son résultat |

Et la règle de dérivation : **le contenu d'un `--help` se relève sur le binaire, jamais recopié en
prose.** Quand une doc doit citer la surface, elle cite ce que la commande **répond**, pas ce dont on se
souvient. Un tableau d'options recopié à la main est un duplicata avec une horloge : il annoncera vingt-six
verbes le jour où il y en aura trente, et personne ne le verra.

> **Le test qui attrape ça** : lancer `<outil> --help` et comparer à ce que la doc affirme. S'ils
> divergent, c'est la doc qui a tort, par construction.

## Quand la surface VARIE selon le palier de build

Si l'artefact existe en paliers (prod, dev, debug, voir `concevoir-avant-coder`), toutes les commandes
ne sont pas présentes partout. C'est le meilleur révélateur de ce skill : **une aide dérivée des
verbes réellement enregistrés est juste dans chaque palier sans un geste de plus**, tandis qu'une aide
écrite à la main se met à mentir **dès le premier palier**, en annonçant ce que le binaire ne contient
pas. Les paliers ne cassent pas la doc dérivée : ils cassent l'autre.

Quatre règles, et l'asymétrie de la deuxième est le point important :

1. **`--help` liste ce que CE build sait faire**, parce qu'il est généré depuis les verbes réellement
   enregistrés. Le README, lui, ne les énumère pas : il renvoie au `--help`. Sinon il faudrait N listes
   écrites à la main, une par palier, et elles divergeraient toutes ;
2. **absent de l'aide mais fonctionnel** est tolérable si c'est **délibéré**, une surface de
   compatibilité : anciens noms, alias, à condition qu'un test verrouille **les deux** formes.
   **Listé dans l'aide mais indisponible est un défaut**, toujours. Les deux erreurs ne se valent pas :
   la première surprend agréablement, la seconde fait échouer quelqu'un qui a suivi la doc ;
3. **un verbe absent de CE palier ne répond pas « commande inconnue ».** C'est la règle « nommer les
   endroits regardés » appliquée aux paliers :

   ```
   # inutile, et faux : la commande existe
   error: unknown command 'specs'

   # utile
   Erreur: 'specs' existe mais n'est pas inclus dans ce build (outils de dev exclus).
   Ce build expose: generate, seed. Pour les outils de lecture: build de dev.
   ```

4. **`--version` dit de quel palier il s'agit** : `1.4.0 (release, sans outils de dev)`. Sans ça, un
   rapport de bug ne permet pas de savoir quel programme a tourné, et on débogue le mauvais. C'est deux
   lignes, et ça sert précisément dans le palier que personne n'exerce à la main.

## La sortie machine, et la règle qui la rend utilisable

Un mode `--json`, `--porcelain` ou `--format=...` n'est pas cosmétique : **c'est ce qui permet de
composer une mesure sans réécrire un motif à la main.** Or un motif écrit à la main n'est pas une mesure,
c'est une devinette qui renvoie un nombre plausible.

**Une sortie machine ne partage JAMAIS son flux avec un diagnostic.** La sortie standard porte la
réponse, la sortie d'erreur porte tout le reste, avertissement, progression, troncature. Une seule
ligne de diagnostic au mauvais endroit et l'analyse de l'appelant échoue : le mode machine devient
inutilisable, donc l'appelant repart au motif écrit à la main, donc on ramène le problème par la porte de
derrière.

Deux pièges qui se ressemblent et se paient pareil :

- **une sous-commande qui ignore `--json` en silence.** Pire qu'absent : l'appelant ne le découvre qu'à
  l'analyse ;
- **un `--json` qui n'est testé sur aucun mode.** Le test qui vaut : **tous** les modes machine doivent
  s'analyser, diagnostics compris. Avec un plancher, s'il n'y a plus aucun mode à tester, le test doit
  refuser de passer au vert.

## Si ton outil produit des artefacts, il doit savoir les relire

Un outil qui **écrit** des journaux, des rapports, des mesures, et qui n'offre **aucune façon de les
relire**, force chaque utilisateur à écrire son propre filtre. Ce n'est pas une gêne, c'est une
multiplication : sur un projet réel, ce défaut précis a produit **89 scripts ad hoc**, chacun avec son
propre périmètre, dont plusieurs faux sans que personne le sache.

La règle : **pour chaque famille d'artefacts produite, un verbe de lecture**, hors ligne, qui ne touche
rien et qui sait rendre du machine. Ce qui remonte alors du même coup : les périmètres divergents, les
fichiers tronqués, les lectures qui rendaient zéro parce qu'elles cherchaient au mauvais endroit. **Un
zéro et « je n'ai pas regardé » sont deux réponses différentes**, et seul un lecteur explicite peut les
distinguer.

## Les messages d'erreur sont de la doc, au moment exact où elle sert

C'est la documentation la plus lue d'un outil, et la moins écrite. Un bon message porte trois choses :
**quoi** (la valeur, pas la catégorie), **où** (le fichier, la ligne, l'identifiant) et **quoi
faire**.

```
# inutile
Error: invalid configuration

# utile
Erreur: 'timeoutMs' vaut -1 dans C:/app/config.local.json (ligne 12).
Attendu: un entier > 0. Valeur par defaut si absent: 30000.
```

Et quand une recherche échoue, **nommer les endroits regardés**. « Fichier introuvable » lance une
enquête ; « introuvable, cherché dans A, B, C » la termine.

## Ce qui reste en prose : dériver, apparier, ou écrire l'écart

- **dériver** : générer la page depuis la source qui fait autorité, signatures, déclarations d'options,
  schéma ;
- **apparier** : un test compare la prose à sa source. Extraire les blocs de commandes du README et les
  **exécuter** en intégration continue est l'appariement le plus rentable qui existe : il attrape les
  exemples périmés, première cause de perte de confiance dans une doc ;
- **écrire l'écart** : quand ni l'un ni l'autre n'est possible, dire dans le document **où il peut
  mentir**. Un document qui annonce ses zones aveugles vaut infiniment mieux qu'un document qu'on croit
  exact.

## Par écosystème, où vit la dérivation

| Besoin | C / C++ | C# / .NET | TypeScript / Node | Rust | Python |
|---|---|---|---|---|---|
| options vers `--help` | `getopt`, CLI11, cxxopts | System.CommandLine | commander, yargs, oclif | clap (dérivé) | argparse, click, typer |
| signatures vers doc | Doxygen | XML doc + DocFX | TypeDoc | rustdoc | Sphinx |
| exemple **exécuté** | tests et extraits compilés en CI | exemples compilés | exemples en CI | **doctests rustdoc** (natif) | **doctest** (natif) |

Rust et Python ont l'exemple exécuté **en standard** : c'est le cran 4 gratuitement. Ailleurs il se
construit, et ça vaut le coup, parce que c'est le seul cran où un exemple faux **casse le build**.

## Anti-patterns, avec leur signature

- **le README qui documente les options.** Signature : il annonce un nombre d'options différent de ce que
  `--help` liste. Toujours dans le sens « le README en oublie » ;
- **le `--help` généré mais jamais relu.** Signature : un mur de drapeaux, aucun exemple, aucune valeur
  par défaut visible. Dérivé donc exact, et inutilisable ;
- **la doc qui vit dans un wiki.** Signature : elle ne bouge pas quand le code bouge, parce qu'elle n'est
  pas dans la revue. Ce qui n'est pas dans le dépôt n'est pas dans le cycle ;
- **l'exemple non exécuté.** Signature : il utilise un drapeau renommé il y a six mois. C'est le plus
  coûteux, parce qu'il fait perdre confiance dans **toute** la doc et pas seulement dans ce bloc ;
- **la mesure par filtre écrit à la main.** Signature : un motif recopié de mémoire, un nombre plausible,
  et personne pour le contredire. C'est le symptôme d'une sortie machine absente ou impure.

## La porte de sortie

Avant de publier l'outil, ces six réponses doivent exister :

1. le `--help` a été **relu comme un livrable** : il porte au moins un exemple, il montre les valeurs par
   défaut, et il se lit sans connaître le code ;
2. le README **ne recopie aucune option**. Ce qu'il garde, c'est ce que `--help` ne peut pas dire : à quoi
   sert l'outil, et par où commencer ;
3. la sortie machine est **pure**, rien d'autre ne sort sur le canal de sortie, et une commande la lit
   sans qu'un humain ait à découper du texte ;
4. les artefacts que l'outil produit, il sait **les relire** : un verbe qui les inspecte existe, sinon la
   seule façon de vérifier une sortie est de la croire ;
5. chaque message d'erreur dit **quoi, où, et comment en sortir**, à l'endroit exact où le lecteur en a
   besoin ;
6. ce qui reste en prose est **apparié par un test**, généré, ou l'écart est écrit avec la condition de
   son retrait.

Et le geste qui résume le skill : **monter d'un cran sur l'échelle, pas écrire moins de doc.** Une page
qui liste des options fait descendre au cran 6 quelque chose qui vivait au cran 2, et le cran 6 est le
seul où un texte peut mentir sans que rien ne casse.
